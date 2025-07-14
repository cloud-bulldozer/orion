"""
run test
"""

import sys
from typing import Any, Dict
from fmatch.matcher import Matcher
from fmatch.logrus import SingletonLogger
from pkg.algorithms import AlgorithmFactory
import pkg.constants as cnsts
from pkg.utils import Utils, get_subtracted_timestamp


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
    elif kwargs["cmr"]:
        algorithm_name = cnsts.CMR
    else:
        algorithm_name = None
    return algorithm_name


def run(**kwargs: dict[str, Any]) -> dict[str, Any]:  # pylint: disable = R0914
    """run method to start the tests

    Args:
        **kwargs: keyword arguments.
            config (str): orion configuration
            es_server (str): elasticsearch endpoint
            output_path (str): output path to save the data
            hunter_analyze (str): changepoint detection through hunter. defaults to True
            output_format (str): output to be table or json
            lookback (str): lookback in days
    Returns:
        tuple:
            - Test output (dict): Test JSON output
            - regression flag (bool): Test result
    """

    logger = SingletonLogger.getLogger("Orion")
    test_config = kwargs["config"]
    es_server = kwargs["es_server"]
    result_output = {}
    regression_flag = False
    # Create fingerprint Matcher
    version_field = "ocpVersion"
    if "version" in test_config:
        version_field = test_config["version"]
    uuid_field = "uuid"
    if "uuid_field" in test_config:
        uuid_field = test_config["uuid_field"]
    
    matcher = Matcher(
        metadata_index=test_config["metadata_index"],
        benchmark_index=test_config["benchmark_index"],
        level=logger.level,
        es_url=es_server,
        verify_certs=False,
        version_field=version_field,
        uuid_field=uuid_field,
    )
    utils = Utils(uuid_field, version_field, matcher)

    start_timestamp = get_subtracted_timestamp(kwargs["lookback"]) if kwargs.get("lookback") else ""
    fingerprint_matched_df, test_config = utils.process_test(test_config, kwargs, start_timestamp)

    if not fingerprint_matched_df:
        sys.exit(3)  # No data present

    algorithm_name = get_algorithm_type(kwargs)
    if algorithm_name is None:
        logger.error("No comparison algorithm configured")
        return None, None
    logger.info("Comparison algorithm: %s", algorithm_name)

    algorithmFactory = AlgorithmFactory()
    algorithm = algorithmFactory.instantiate_algorithm(
        algorithm_name,
        matcher,
        fingerprint_matched_df,
        test_config,
        kwargs,
        metrics_config,
    )
    testname, result_data, test_flag = algorithm.output(kwargs["output_format"])
    result_output[testname] = result_data
    regression_flag = regression_flag or test_flag
    return result_output, regression_flag
