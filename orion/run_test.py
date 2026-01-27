"""
run test
"""
import os
import sys
import json
import copy
import re
import concurrent.futures
from typing import Any, Dict, Tuple
from tabulate import tabulate
from orion.matcher import Matcher
from orion.logger import SingletonLogger
from orion.algorithms import AlgorithmFactory
import orion.constants as cnsts
from orion.utils import Utils, get_subtracted_timestamp, json_to_junit
from orion.github_client import GitHubClient

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
def run(**kwargs: dict[str, Any]) -> Tuple[Tuple[Dict[str, Any], bool, Any, Any, int],
                                          Tuple[Dict[str, Any], bool, Any, Any, int]]:
    """run method to start the tests

    Args:
      **kwargs: keyword arguments
        config (str): file path to config file
        es_server (str): elasticsearch endpoint
        output_path (str): output path to save the data
        hunter_analyze (bool): changepoint detection through hunter. defaults to True
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

    logger = SingletonLogger.get_logger("Orion")
    result_output, regression_flag, regression_data = {}, False, []
    result_output_pull, regression_flag_pull, regression_data_pull = {}, False, []
    average_values_df_pull, average_values_df = "", ""
    pr = 0
    for test in config["tests"]:
        # Create fingerprint Matcher
        if "metadata" in test:
            if "pullNumber" in test["metadata"] and test["metadata"]["pullNumber"] > 0:
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
                    result_output_pull = futures_pull.result()[0]
                    regression_flag_pull = futures_pull.result()[1]
                    regression_data_pull = futures_pull.result()[2]
                    average_values_df_pull = futures_pull.result()[3]
                    result_output = futures_periodic.result()[0]
                    regression_flag = futures_periodic.result()[1]
                    regression_data = futures_periodic.result()[2]
                    average_values_df = futures_periodic.result()[3]
            else:
                result_output, regression_flag, regression_data, average_values_df = analyze(
                    test,
                    kwargs
                )
    results_pull = (
        result_output_pull,
        regression_flag_pull,
        regression_data_pull,
        average_values_df_pull,
        pr
    )
    results = (
        result_output,
        regression_flag,
        regression_data,
        average_values_df,
        0
    )
    return results, results_pull


def get_start_timestamp(kwargs: Dict[str, Any], test: Dict[str, Any], is_pull: bool) -> str:
    """Get the start timestamp if lookback is provided."""
    logger = SingletonLogger.get_logger("Orion")
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
        max_early_index: Maximum index (0-based) to consider as "early" (default: 5, meaning first 5 points)
    
    Returns:
        bool: True if any changepoint is in the first max_early_index points
    """
    for index, result in enumerate(result_data_json):
        if index < max_early_index and result.get("is_changepoint", False):
            return True
    return False


def has_late_changepoint(result_data_json: list, max_late_index: int = 5) -> bool:
    """Check if any changepoint is detected in the last N data points.
    
    Args:
        result_data_json: List of result dictionaries from algorithm output
        max_late_index: Number of points from the end to consider as "late" (default: 5, meaning last 5 points)
    
    Returns:
        bool: True if any changepoint is in the last max_late_index points
    """
    total_points = len(result_data_json)
    if total_points == 0:
        return False
    
    # Calculate the starting index for "late" points
    late_start_index = total_points - max_late_index
    
    for index, result in enumerate(result_data_json):
        if index >= late_start_index and result.get("is_changepoint", False):
            return True
    return False


def increase_lookback(lookback_str: str, days_to_add: int = 10) -> str:
    """Increase lookback duration by adding days.
    
    Args:
        lookback_str: Lookback string in format like "15d" or "20d"
        days_to_add: Number of days to add (default: 10)
    
    Returns:
        str: New lookback string with increased days
    """
    if not lookback_str:
        return f"{days_to_add}d"
    
    # Parse the lookback string (format: Xd or XdYh)
    reg_ex = re.match(r"^(?:(\d+)d)?(?:(\d+)h)?$", lookback_str)
    if not reg_ex:
        # If format is invalid, just add the days
        return f"{days_to_add}d"
    
    days = int(reg_ex.group(1)) if reg_ex.group(1) else 0
    hours = int(reg_ex.group(2)) if reg_ex.group(2) else 0
    
    # Add the extra days
    new_days = days + days_to_add
    
    # Reconstruct the string
    if hours > 0:
        return f"{new_days}d{hours}h"
    return f"{new_days}d"

def analyze(test, kwargs, is_pull = False) -> Tuple[Dict[str, Any], bool, Any, Any]:
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
    logger.info("=" * 80)
    logger.info("USING UPDATED CODE: Windowing logic enabled (early/late changepoint detection)")
    logger.info("=" * 80)
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
            return None, None, None, None
        sys.exit(3) # No data present

    metrics = []
    for metric_name, _ in metrics_config.items():
        metrics.append(metric_name)

    algorithm_name = get_algorithm_type(kwargs)
    if algorithm_name is None:
        logger.error("No algorithm configured")
        return None, None, None, None
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
    # This is env is only present in prow ci
    prow_job_id = os.getenv("PROW_JOB_ID")
    if kwargs["output_format"] != cnsts.JSON and prow_job_id and prow_job_id.strip():
        testname, result_data, _ = algorithm.output(cnsts.JSON)
        output_file_name = f"{kwargs['save_output_path'].split('.')[0]}_{testname}.json"
        with open(output_file_name, 'w', encoding="utf-8") as file:
            file.write(str(result_data))

    testname, result_data, test_flag = algorithm.output(kwargs["output_format"])
    result_output[testname] = result_data
    
    # Query with JSON to check for early and late changepoints
    regression_data = []
    if test_flag:
        logger.info(">>> WINDOWING LOGIC: Checking for early/late changepoints...")
        testname, result_data, test_flag = algorithm.output(cnsts.JSON)
        result_data_json = json.loads(result_data)
        logger.info(">>> WINDOWING LOGIC: Total data points: %d", len(result_data_json))
        
        # Check if any changepoint is in the last 5 data points (insufficient future data)
        # This check happens BEFORE window expansion - if late, ignore immediately
        # Note: If this is a real changepoint, it will be properly detected in the next cycle
        # when more future data is available and it's no longer in the last 5 points
        if has_late_changepoint(result_data_json, max_late_index=5):
            logger.warning(">>> WINDOWING LOGIC: LATE CHANGEPOINT DETECTED in last 5 data points!")
            logger.warning("Changepoint detected in last 5 data points. Insufficient future data to validate. "
                         "Ignoring changepoint to avoid false positives. "
                         "If this is a real changepoint, it will be detected in the next cycle when more data is available.")
            # Don't flag as regression if changepoint is at the end
            test_flag = False
        # Check if any changepoint is in the first 5 data points (needs validation with more history)
        elif has_early_changepoint(result_data_json, max_early_index=5):
            logger.info(">>> WINDOWING LOGIC: EARLY CHANGEPOINT DETECTED in first 5 data points!")
            logger.info("Early changepoint detected in first 5 data points. Expanding lookback window by 10 days and increasing lookback-size to ensure 5 samples before changepoint.")
            
            # Create a copy of kwargs with expanded lookback and lookback-size
            expanded_kwargs = copy.deepcopy(kwargs)
            original_lookback = kwargs.get("lookback", "")
            expanded_lookback = increase_lookback(original_lookback, days_to_add=10)
            expanded_kwargs["lookback"] = expanded_lookback
            
            # Calculate required lookback-size: current points + 5 (to ensure 5 points before changepoint)
            current_points = len(fingerprint_matched_df)
            required_lookback_size = current_points + 5
            original_lookback_size = kwargs.get("lookback_size", 10000)
            expanded_kwargs["lookback_size"] = required_lookback_size
            
            logger.info("Original lookback: %s, Expanded lookback: %s", original_lookback, expanded_lookback)
            logger.info("Original lookback-size: %s, Expanded lookback-size: %s (current points: %s + 5)", 
                       original_lookback_size, required_lookback_size, current_points)
            
            # Re-run analysis with expanded lookback window
            expanded_start_timestamp = get_start_timestamp(expanded_kwargs, test, is_pull)
            expanded_fingerprint_matched_df, _ = utils.process_test(
                test,
                matcher,
                expanded_kwargs,
                expanded_start_timestamp
            )
            
            if expanded_fingerprint_matched_df is not None and len(expanded_fingerprint_matched_df) > len(fingerprint_matched_df):
                # Isolation forest requires no null values in the dataframe
                if algorithm_name == cnsts.ISOLATION_FOREST:
                    expanded_fingerprint_matched_df = expanded_fingerprint_matched_df.dropna().reset_index()
                
                # Re-run algorithm with expanded data
                expanded_algorithm = algorithmFactory.instantiate_algorithm(
                    algorithm_name,
                    expanded_fingerprint_matched_df,
                    test,
                    expanded_kwargs,
                    metrics_config,
                )
                
                expanded_testname, expanded_result_data, expanded_test_flag = expanded_algorithm.output(cnsts.JSON)
                expanded_result_data_json = json.loads(expanded_result_data)
                
                # Check if changepoint still exists after expansion
                if expanded_test_flag:
                    logger.info(">>> WINDOWING LOGIC: Changepoint CONFIRMED after expansion - flagging as regression")
                    logger.info("Changepoint still detected after expanding lookback window. Flagging as regression.")
                    # Use the expanded results
                    result_data_json = expanded_result_data_json
                    test_flag = expanded_test_flag
                    # Update result_output with expanded data
                    expanded_testname, expanded_result_data_formatted, _ = expanded_algorithm.output(kwargs["output_format"])
                    result_output[expanded_testname] = expanded_result_data_formatted
                else:
                    logger.info(">>> WINDOWING LOGIC: Changepoint DISMISSED after expansion - was false positive")
                    logger.info("No changepoint detected after expanding lookback window. "
                              "Original changepoint was likely a false positive. Not flagging as regression.")
                    # No changepoint after expansion, so don't flag as regression
                    test_flag = False
                    result_data_json = expanded_result_data_json
            else:
                logger.warning("Expanded lookback did not retrieve additional data. "
                             "Proceeding with original analysis results.")
                # Use original results if expansion didn't help
                result_data_json = result_data_json
        
        # Process regression data from final results
        if test_flag:
            logger.info(">>> WINDOWING LOGIC: Processing regression data (changepoint validated)")
        else:
            logger.info(">>> WINDOWING LOGIC: No regression (changepoint filtered or dismissed)")
            prev_ver = None
            bad_ver = None
            for result in result_data_json:
                if result["is_changepoint"]:
                    bad_ver = result[test["version_field"]]
                else:
                    prev_ver = result[test["version_field"]]
                if prev_ver is not None and bad_ver is not None:
                    if sippy_pr_search:
                        prs = Utils().sippy_pr_diff(prev_ver, bad_ver)
                        doc = {"prev_ver": prev_ver,
                                "bad_ver": bad_ver}
                        # We have seen where sippy_pr_diff returns an empty list of PRs
                        # since there is a change the payload tests have not completed.
                        if prs:
                            doc["prs"] = prs
                        regression_data.append(doc)
                    else:
                        regression_data.append({
                            "prev_ver": prev_ver,
                            "bad_ver": bad_ver,
                            "prs": []
                        })
                    prev_ver = None
                    bad_ver = None

    regression_flag = regression_flag or test_flag
    return result_output, regression_flag, regression_data, average_values


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
    data = ["0000-00-00 00:00:00 +0000",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "x" * len(last_row[version_field])]
    for metric, value in avg_data.items():
        headers.append(metric)
        data.append(value)
    if display_fields:
        for display_field in display_fields:
            headers.append(display_field)
            data.append("x" * len(last_row[display_field]))
    return tabulate([data], headers=headers, tablefmt="simple",
                    floatfmt=[".2f", ".5f", ".6f", ".5f", ".5f", ".4f"])
