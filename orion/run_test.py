"""
run test
"""
import os
import sys
import json
import copy
import concurrent.futures
from typing import Any, Dict, Tuple
from tabulate import tabulate
from orion.matcher import Matcher
from orion.logger import SingletonLogger
from orion.algorithms import AlgorithmFactory
import orion.constants as cnsts
from orion.utils import Utils, get_subtracted_timestamp, json_to_junit

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

        version_field = "ocpVersion"
        if "version" in test:
            version_field=test["version"]
        uuid_field = "uuid"
        if "uuid_field" in test:
            uuid_field=test["uuid_field"]
        if "metadata" in test and "jobType" in test["metadata"]:
            if test["metadata"]["jobType"] == "pull":
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    logger.info("Executing tasks in parallel...")
                    futures_pull = executor.submit(analyze, test, kwargs,
                                                   version_field, uuid_field)
                    pr = test["metadata"]["pullNumber"]
                    test_periodic = copy.deepcopy(test)
                    test_periodic["metadata"]["jobType"] = "periodic"
                    test_periodic["metadata"]["pullNumber"] = 0
                    # remove organization and repository from the metadata to
                    # be able to compare with the periodic cases
                    test_periodic["metadata"]["organization"] = ""
                    test_periodic["metadata"]["repository"] = ""
                    futures_periodic = executor.submit(analyze, test_periodic, kwargs,
                                                       version_field, uuid_field)
                    concurrent.futures.wait([futures_pull, futures_periodic])
                    result_output_pull = futures_pull.result()[0]
                    regression_flag_pull = futures_pull.result()[1]
                    regression_data_pull = futures_pull.result()[2]
                    average_values_df_pull = futures_pull.result()[3]
                    result_output = futures_periodic.result()[0]
                    regression_flag = futures_periodic.result()[1]
                    regression_data = futures_periodic.result()[2]
                    average_values_df = futures_periodic.result()[3]
        elif "metadata" in test:
            result_output, regression_flag, regression_data, average_values_df = analyze(
                    test,
                    kwargs,
                    version_field,
                    uuid_field
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


def get_start_timestamp(kwargs: Dict[str, Any]) -> str:
    """Get the start timestamp if lookback is provided."""
    if kwargs["since"] != "" and kwargs["since"] is not None:
        if kwargs.get("lookback"):
            return get_subtracted_timestamp(kwargs["lookback"], kwargs["since"])
        return ""
    return (
        get_subtracted_timestamp(kwargs["lookback"]) if kwargs.get("lookback") else ""
    )

def analyze(
            test,
            kwargs,
            version_field,
            uuid_field
        ) -> Tuple[Dict[str, Any], bool, Any, Any]:
    """
    Utils class to process the test

    Args:
        test: test object
        kwargs: keyword arguments
        version_field: version field
        uuid_field: uuid field
    """
    matcher = Matcher(
        index=kwargs["metadata_index"],
        es_server=kwargs["es_server"],
        verify_certs=False,
        version_field=version_field,
        uuid_field=uuid_field
    )
    utils = Utils(uuid_field, version_field)
    logger = SingletonLogger.get_logger("Orion")
    sippy_pr_search = kwargs["sippy_pr_search"]
    result_output = {}
    regression_flag = False
    start_timestamp = get_start_timestamp(kwargs)
    fingerprint_matched_df, metrics_config = utils.process_test(
        test,
        matcher,
        kwargs,
        start_timestamp
    )

    if fingerprint_matched_df is None:
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
            uuid_field=uuid_field,
            average=True)
    else:
        average_values = tabulate_average_values(
            avg_values,
            fingerprint_matched_df.iloc[-1],
            version_field,
            uuid_field)

    algorithmFactory = AlgorithmFactory()
    algorithm = algorithmFactory.instantiate_algorithm(
            algorithm_name,
            matcher,
            fingerprint_matched_df,
            test,
            kwargs,
            metrics_config,
            version_field,
            uuid_field
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
    # Query with JSON
    regression_data = []
    if test_flag:
        testname, result_data, test_flag = algorithm.output(cnsts.JSON)
        prev_ver = None
        bad_ver = None
        for result in json.loads(result_data):
            if result["is_changepoint"]:
                bad_ver = result[version_field]
            else:
                prev_ver = result[version_field]
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
        uuid_field="uuid"
        ) -> str:
    """Tabulate the average values

    Args:
        avg_data: average data
        last_row: last row of the dataframe

    Returns:
        str: tabulated average values
    """
    headers = ["time", uuid_field, version_field, "buildUrl"]
    data = ["0000-00-00 00:00:00 +0000",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "x" * len(last_row[version_field]),
            "x" * len(last_row["buildUrl"])]
    for metric, value in avg_data.items():
        headers.append(metric)
        data.append(value)
    return tabulate([data], headers=headers, tablefmt="simple",
                    floatfmt=[".2f", ".5f", ".6f", ".5f", ".5f", ".4f"])
