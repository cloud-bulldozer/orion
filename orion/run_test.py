"""
run test
"""
import os
import sys
import json
import copy
from typing import Any, Dict, Tuple
from orion.matcher import Matcher
from orion.logger import SingletonLogger
from orion.algorithms import AlgorithmFactory
import orion.constants as cnsts
from orion.utils import Utils, get_subtracted_timestamp
import concurrent.futures

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
def run(**kwargs: dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
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
        tuple:
            - Test output (dict): Test JSON output
            - regression flag (bool): Test result
    """
    logger = SingletonLogger.get_logger("Orion")
    config = kwargs["config"]
    
    for test in config["tests"]:
        # Create fingerprint Matcher

        version_field = "ocpVersion"
        if "version" in test:
            version_field=test["version"]
        uuid_field = "uuid"
        if "uuid_field" in test:
            uuid_field=test["uuid_field"]

        result_output, regression_flag, regression_data = {}, False, []
        if "metadata" in test and "jobType" in test["metadata"]:
            if test["metadata"]["jobType"] == "pull":
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    print("Executing tasks in parallel...")
                    futures_pull = executor.submit(analyze, test, kwargs, version_field, uuid_field)
                    test_periodic = copy.deepcopy(test)
                    test_periodic["metadata"]["jobType"] = "periodic"
                    test_periodic["metadata"]["pullNumber"] = 0
                    futures_periodic = executor.submit(analyze, test_periodic, kwargs, version_field, uuid_field)
                    concurrent.futures.wait([futures_pull, futures_periodic])
                    print("Results Pull:")
                    print(futures_pull.result())
                    print("Results Periodic:")
                    print(futures_periodic.result())
                    result_output = {**futures_pull.result()[0], **futures_periodic.result()[0]}
                    regression_flag = futures_pull.result()[1] or futures_periodic.result()[1]
                    regression_data = futures_pull.result()[2] + futures_periodic.result()[2]
            else:
                result_output, regression_flag, regression_data = analyze(
                        test,
                        kwargs,
                        version_field,
                        uuid_field
                    )
    return result_output, regression_flag, regression_data


def get_start_timestamp(kwargs: Dict[str, Any]) -> str:
    """Get the start timestamp if lookback is provided."""
    return (
        get_subtracted_timestamp(kwargs["lookback"]) if kwargs.get("lookback") else ""
    )

def analyze(
            test,
            kwargs,
            version_field,
            uuid_field,
        ) -> Tuple[Dict[str, Any], bool, Any]:
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
    print("Test: ", test)
    fingerprint_matched_df, metrics_config = utils.process_test(
        test,
        matcher,
        kwargs,
        start_timestamp
    )

    if fingerprint_matched_df is None:
        sys.exit(3) # No data present

    algorithm_name = get_algorithm_type(kwargs)
    if algorithm_name is None:
        logger.error("No algorithm configured")
        return None, None, None
    logger.info("Comparison algorithm: %s", algorithm_name)

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
                            regression_data.append({
                                "prev_ver": prev_ver,
                                "bad_ver": bad_ver,
                                "prs": prs})
                    else:
                        regression_data.append({
                            "prev_ver": prev_ver,
                            "bad_ver": bad_ver,
                            "prs": []
                        })
                    prev_ver = None
                    bad_ver = None

    regression_flag = regression_flag or test_flag
    return result_output, regression_flag, regression_data