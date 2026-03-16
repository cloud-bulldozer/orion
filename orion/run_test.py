"""
run test
"""
import os
import sys
import json
import copy
import concurrent.futures
from typing import Any, Dict, NamedTuple, Optional, Tuple
from tabulate import tabulate
from orion.matcher import Matcher
from orion.logger import SingletonLogger
from orion.algorithms import AlgorithmFactory
import orion.constants as cnsts
from orion.utils import Utils, get_subtracted_timestamp, json_to_junit
from orion.github_client import GitHubClient
from orion.visualization import VizData


class AnalyzeResult(NamedTuple):
    """Return type for analyze()."""
    output: Optional[Dict[str, Any]]
    regression_flag: Optional[bool]
    regression_data: Optional[list]
    average_values: Any
    viz_data: Any


class TestResults(NamedTuple):
    """Return type for run() results tuples."""
    output: Optional[Dict[str, Any]]
    regression_flag: bool
    regression_data: list
    average_values: Any
    pr: int
    viz_data: list


def get_algorithm_type(kwargs):
    """Switch Case of getting algorithm name

    Args:
        kwargs (dict): passed command line arguments

    Returns:
        str: algorithm name
    """
    if kwargs["hunter_analyze"]:
        algorithm_name = cnsts.EDIVISIVE
    elif kwargs["anomaly_detection"]:
        algorithm_name = cnsts.ISOLATION_FOREST
    elif kwargs['cmr']:
        algorithm_name = cnsts.CMR
    else:
        algorithm_name = None
    return algorithm_name

# pylint: disable=too-many-locals
def run(**kwargs: dict[str, Any]) -> Tuple[TestResults, TestResults]:
    """run method to start the tests

    Args:
      **kwargs: keyword arguments
        config (str): file path to config file
        es_server (str): elasticsearch endpoint
        output_path (str): output path to save the data
        hunter_analyze (bool): changepoint detection through apache_otava. defaults to True
        output_format (str): output to be table or json
        lookback (str): lookback in days

    Returns:
        Two tuple objects containing the results of the tests
        tuple:
            - Test output (dict): Test JSON output
            - regression flag (bool): Test result
            - regression data (list): Regression data
    """
    config = kwargs["config"]
    pr_analysis = kwargs["pr_analysis"]

    logger = SingletonLogger.get_logger("Orion")
    result_output, regression_flag, regression_data = {}, False, []
    result_output_pull, regression_flag_pull, regression_data_pull = {}, False, []
    average_values_df_pull, average_values_df = "", ""
    all_viz_data = []
    pr = 0
    for test in config["tests"]:
        # Create fingerprint Matcher
        if "metadata" in test:
            if pr_analysis:
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    logger.info("Executing tasks in parallel...")
                    logger.info("Ensuring jobType is set to pull")
                    test["metadata"]["jobType"] = "pull"
                    futures_pull = executor.submit(analyze, test, kwargs, True)
                    pr = test["metadata"]["pullNumber"]
                    test_periodic = copy.deepcopy(test)
                    test_periodic["metadata"]["jobType"] = "periodic"
                    test_periodic["metadata"]["pullNumber"] = 0
                    # remove organization and repository from the metadata to
                    # be able to compare with the periodic cases
                    test_periodic["metadata"]["organization"] = ""
                    test_periodic["metadata"]["repository"] = ""
                    futures_periodic = executor.submit(analyze, test_periodic, kwargs, False)
                    concurrent.futures.wait([futures_pull, futures_periodic])
                    pull_result = futures_pull.result()
                    periodic_result = futures_periodic.result()
                    result_output_pull = pull_result.output
                    regression_flag_pull = pull_result.regression_flag
                    regression_data_pull = pull_result.regression_data
                    average_values_df_pull = pull_result.average_values
                    result_output = periodic_result.output
                    regression_flag = periodic_result.regression_flag
                    regression_data = periodic_result.regression_data
                    average_values_df = periodic_result.average_values
                    if pull_result.viz_data is not None:
                        all_viz_data.append(pull_result.viz_data)
                    if periodic_result.viz_data is not None:
                        all_viz_data.append(periodic_result.viz_data)
            else:
                (result_output, regression_flag,
                 regression_data, average_values_df,
                 viz_data) = analyze(test, kwargs)
                if viz_data is not None:
                    all_viz_data.append(viz_data)
    results_pull = TestResults(
        output=result_output_pull,
        regression_flag=regression_flag_pull,
        regression_data=regression_data_pull,
        average_values=average_values_df_pull,
        pr=pr,
        viz_data=[],
    )
    results = TestResults(
        output=result_output,
        regression_flag=regression_flag,
        regression_data=regression_data,
        average_values=average_values_df,
        pr=0,
        viz_data=all_viz_data,
    )
    return results, results_pull


def get_start_timestamp(kwargs: Dict[str, Any], test: Dict[str, Any], is_pull: bool) -> str:
    """Get the start timestamp if lookback is provided."""
    logger = SingletonLogger.get_logger("Orion")
    # Window expansion: unbounded lookback only for non-PR. For PR we keep PR creation.
    if kwargs.get("_unbounded_lookback"):
        return ""
    if is_pull:
        logger.info("Getting start timestamp from pull request creation date")
        client = GitHubClient(repositories=[])
        creation_date = client.get_pr_creation_date(test["metadata"]["organization"],
                                                    test["metadata"]["repository"],
                                                    test["metadata"]["pullNumber"])
        if creation_date:
            logger.info("Start timestamp from pull request creation date: %s",
                        creation_date.strftime("%Y-%m-%dT%H:%M:%SZ"))
            return creation_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    if kwargs["since"] != "" and kwargs["since"] is not None:
        if kwargs.get("lookback"):
            return get_subtracted_timestamp(kwargs["lookback"], kwargs["since"])
        return ""
    return (
        get_subtracted_timestamp(kwargs["lookback"]) if kwargs.get("lookback") else ""
    )

def has_early_changepoint(result_data_json: list, max_early_index: int = 5) -> bool:
    """Check if any changepoint is detected in the first N data points.

    Args:
        result_data_json: List of result dictionaries from algorithm output
        max_early_index: Maximum index (0-based) to consider as "early"
            (default: 5, meaning first 5 points)

    Returns:
        bool: True if any changepoint is in the first max_early_index points
    """
    for index, result in enumerate(result_data_json):
        if index < max_early_index and result.get("is_changepoint", False):
            return True
    return False


def clear_early_changepoints(result_data_json: list, max_early_index: int) -> None:
    """Clear changepoint flags in the first N points so table output shows no regression.

    Modifies result_data_json in place: sets is_changepoint=False and
    percentage_change=0 for each record in the buffer that was marked as changepoint.
    """
    for index, result in enumerate(result_data_json):
        if index < max_early_index and result.get("is_changepoint", False):
            result["is_changepoint"] = False
            if "metrics" in result:
                for metric_data in result["metrics"].values():
                    metric_data["percentage_change"] = 0


def analyze(test, kwargs, is_pull = False) -> AnalyzeResult:
    """
    Utils class to process the test

    Args:
        test: test object
        kwargs: keyword arguments
    """
    matcher = Matcher(
        index=kwargs["metadata_index"] or test["metadata_index"],
        es_server=kwargs["es_server"],
        verify_certs=False,
        version_field=test["version_field"],
        uuid_field=test["uuid_field"]
    )
    utils = Utils(test["uuid_field"], test["version_field"])
    logger = SingletonLogger.get_logger("Orion")
    sippy_pr_search = kwargs["sippy_pr_search"]
    result_output = {}
    regression_flag = False
    start_timestamp = get_start_timestamp(kwargs, test, is_pull)
    fingerprint_matched_df, metrics_config = utils.process_test(
        test,
        matcher,
        kwargs,
        start_timestamp
    )

    if fingerprint_matched_df is None:
        if is_pull:
            return AnalyzeResult(None, None, None, None, None)
        sys.exit(3) # No data present

    metrics = []
    for metric_name, _ in metrics_config.items():
        metrics.append(metric_name)

    algorithm_name = get_algorithm_type(kwargs)
    if algorithm_name is None:
        logger.error("No algorithm configured")
        return AnalyzeResult(None, None, None, None, None)
    logger.info("Comparison algorithm: %s", algorithm_name)

    # Isolation forest requires no null values in the dataframe
    if algorithm_name == cnsts.ISOLATION_FOREST:
        fingerprint_matched_df = fingerprint_matched_df.dropna().reset_index()

    avg_values = fingerprint_matched_df[metrics].mean()
    if kwargs['output_format'] == cnsts.JSON:
        average_values = avg_values.to_json()
    elif kwargs['output_format'] == cnsts.JUNIT:
        average_values = json_to_junit(
            test_name=test["name"]+"_average",
            data_json=avg_values.to_json(),
            metrics_config=metrics_config,
            uuid_field=test["uuid_field"],
            average=True)
    else:
        if len(fingerprint_matched_df) > 0:
            average_values = tabulate_average_values(
                avg_values,
                fingerprint_matched_df.iloc[-1],
                test["version_field"],
                test["uuid_field"],
                kwargs.get("display", []))
        else:
            average_values = ""

    algorithmFactory = AlgorithmFactory()
    algorithm = algorithmFactory.instantiate_algorithm(
            algorithm_name,
            fingerprint_matched_df,
            test,
            kwargs,
            metrics_config,
        )
    expanded_algorithm = None
    # This is env is only present in prow ci
    prow_job_id = os.getenv("PROW_JOB_ID")
    if kwargs["output_format"] != cnsts.JSON and prow_job_id and prow_job_id.strip():
        testname, result_data, _ = algorithm.output(cnsts.JSON)
        output_file_name = f"{os.path.splitext(kwargs['save_output_path'])[0]}_{testname}.json"
        with open(output_file_name, 'w', encoding="utf-8") as file:
            file.write(str(result_data))

    testname, result_data, test_flag = algorithm.output(kwargs["output_format"])
    result_output[testname] = result_data
    # Query with JSON
    regression_data = []
    if test_flag:
        testname, result_data, test_flag = algorithm.output(cnsts.JSON)
        result_data_json = json.loads(result_data)
        current_points = len(fingerprint_matched_df)

        changepoint_buffer = cnsts.CHANGEPOINT_BUFFER
        if changepoint_buffer > 0 and has_early_changepoint(
                result_data_json, max_early_index=changepoint_buffer
        ):
            logger.info(
                "Changepoint in buffer (first %d points): attempting "
                "window expansion for test=%s",
                changepoint_buffer,
                test["name"],
            )
            expanded_kwargs = copy.deepcopy(kwargs)
            # Unbounded lookback (non-PR) or keep PR creation (PR): get up to 5 more
            # points; cap at current + EXPAND_POINTS.
            expanded_kwargs["lookback"] = ""
            if not is_pull:
                expanded_kwargs["_unbounded_lookback"] = True
            required_lookback_size = current_points + cnsts.EXPAND_POINTS
            expanded_kwargs["lookback_size"] = required_lookback_size
            logger.info(
                "Window expansion: unbounded lookback, lookback_size -> %d",
                required_lookback_size,
            )

            expanded_start_timestamp = get_start_timestamp(
                expanded_kwargs, test, is_pull
            )
            # Reset matcher to metadata index for executing expanded window analysis.
            matcher.index = expanded_kwargs.get("metadata_index") or test.get("metadata_index")
            expanded_fingerprint_matched_df, _ = utils.process_test(
                test,
                matcher,
                expanded_kwargs,
                expanded_start_timestamp
            )

            expanded_points = (
                len(expanded_fingerprint_matched_df)
                if expanded_fingerprint_matched_df is not None
                else 0
            )

            if (expanded_fingerprint_matched_df is not None and
                    expanded_points > len(fingerprint_matched_df)):
                if algorithm_name == cnsts.ISOLATION_FOREST:
                    expanded_fingerprint_matched_df = (
                        expanded_fingerprint_matched_df
                        .dropna()
                        .reset_index()
                    )

                expanded_algorithm = algorithmFactory.instantiate_algorithm(
                    algorithm_name,
                    expanded_fingerprint_matched_df,
                    test,
                    expanded_kwargs,
                    metrics_config,
                )

                (expanded_testname, expanded_result_data,
                 expanded_test_flag) = expanded_algorithm.output(cnsts.JSON)
                expanded_result_data_json = json.loads(expanded_result_data)

                if expanded_test_flag:
                    logger.info(
                        "Window expansion: expanded run still has changepoint; "
                        "using expanded results (test=%s)",
                        test["name"],
                    )
                    result_data_json = expanded_result_data_json
                    test_flag = expanded_test_flag
                    (expanded_testname, expanded_result_data_formatted, _) = (
                        expanded_algorithm.output(kwargs["output_format"])
                    )
                    result_output[expanded_testname] = expanded_result_data_formatted
                else:
                    test_flag = False
                    result_data_json = expanded_result_data_json
                    (_, expanded_result_data_formatted, _) = (
                        expanded_algorithm.output(kwargs["output_format"])
                    )
                    result_output[expanded_testname] = expanded_result_data_formatted
            else:
                logger.info(
                    "Window expansion: no additional data (original=%d, "
                    "expanded=%d); skipping early changepoint (test=%s)",
                    current_points,
                    expanded_points,
                    test["name"],
                )
                test_flag = False
                clear_early_changepoints(result_data_json, changepoint_buffer)
                # Use a copy of cleared data for output so table/JSON/JUnit show no changepoint
                cleared_json = copy.deepcopy(result_data_json)
                if kwargs["output_format"] == cnsts.TEXT:
                    # result_output[testname] = algorithm.format_table_from_json(
                    #     cleared_json
                    # )
                    testname, result_data, _ = algorithm.output(cnsts.TEXT)
                    result_output[testname] = result_data
                elif kwargs["output_format"] == cnsts.JSON:
                    result_output[testname] = json.dumps(
                        cleared_json, indent=2
                    )
                elif kwargs["output_format"] == cnsts.JUNIT:
                    result_output[testname] = json_to_junit(
                        test_name=testname,
                        data_json=cleared_json,
                        metrics_config=metrics_config,
                        uuid_field=test["uuid_field"],
                        display_fields=kwargs.get("display"),
                    )

        if test_flag:
            logger.info(
                "Regression reported: changepoint validated (test=%s)",
                test["name"],
            )
            for index, result in enumerate(result_data_json):
                prev_ver = None
                bad_ver = None
                if result["is_changepoint"]:
                    bad_ver = result[test["version_field"]]
                    if index > 0:
                        prior = result_data_json[index - 1]
                        prev_ver = prior[test["version_field"]]
                else:
                    continue

                metrics_with_change = []
                for metric_name, metric_data in result["metrics"].items():
                    if metric_data.get("percentage_change", 0) != 0:
                        metrics_with_change.append({
                            "name": metric_name,
                            "value": metric_data.get("value"),
                            "percentage_change": metric_data.get("percentage_change", 0),
                            "labels": metric_data.get("labels", [])
                        })

                github_context = result.get("github_context")
                prs = result.get("prs")

                doc = {
                    "test_name": test["name"],
                    "prev_ver": prev_ver,
                    "bad_ver": bad_ver,
                    "metrics_with_change": metrics_with_change,
                    "prs": [],
                    "github_context": None
                    }
                if github_context is not None:
                    doc["github_context"] = github_context
                if prs is not None:
                    doc["prs"] = prs
                if sippy_pr_search:
                    prs = Utils().sippy_pr_diff(prev_ver, bad_ver)
                    if prs:
                        doc["prs"] = prs
                regression_data.append(doc)

    regression_flag = regression_flag or test_flag

    viz_data = None
    if kwargs.get("viz"):
        # Use the algorithm that produced the final results: expanded_algorithm
        # when window expansion succeeded, otherwise the original algorithm.
        viz_algorithm = expanded_algorithm if expanded_algorithm is not None else algorithm
        _, change_points_by_metric = viz_algorithm.get_analysis_results()
        acked_entries = []
        ack_map = viz_algorithm.options.get("ackMap")
        if ack_map is not None:
            acked_entries = ack_map.get("ack", [])
        viz_data = VizData(
            test_name=test["name"],
            dataframe=viz_algorithm.dataframe.copy(),
            metrics_config=metrics_config,
            change_points_by_metric=change_points_by_metric,
            uuid_field=test["uuid_field"],
            version_field=test["version_field"],
            acked_entries=acked_entries,
        )

    return AnalyzeResult(result_output, regression_flag, regression_data, average_values, viz_data)


def tabulate_average_values(
        avg_data,
        last_row,
        version_field="ocpVersion",
        uuid_field="uuid",
        display_fields=None
        ) -> str:
    """Tabulate the average values

    Args:
        avg_data: average data
        last_row: last row of the dataframe

    Returns:
        str: tabulated average values
    """
    headers = ["time", uuid_field, version_field]
    if version_field in last_row :
        data = ["0000-00-00 00:00:00 +0000",
                "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "x" * len(last_row[version_field])]
    else :
        data = ["0000-00-00 00:00:00 +0000",
                "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "x" * len("No Version")]
    for metric, value in avg_data.items():
        headers.append(metric)
        data.append(value)
    if display_fields:
        for display_field in display_fields:
            headers.append(display_field)
            data.append("x" * len(last_row[display_field]))
    return tabulate([data], headers=headers, tablefmt="simple",
                    floatfmt=[".2f", ".5f", ".6f", ".5f", ".5f", ".4f"])
