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
    elif kwargs['cmr']:
        algorithm_name = cnsts.CMR
    else:
        algorithm_name = None
    return algorithm_name

def run(**kwargs: dict[str, Any]) -> dict[str, Any]: #pylint: disable = R0914
    """run method to start the tests

    Args:
        config (_type_): file path to config file
        output_path (_type_): output path to save the data
        hunter_analyze (_type_): changepoint detection through hunter. defaults to True
        output_format (_type_): output to be table or json

    Returns:
        _type_: _description_
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    config_map = kwargs["configMap"]
    result_output = {}
    regression_flag = False
    for test in config_map["tests"]:
        # Create fingerprint Matcher

        version_field = "ocpVersion"
        if "version" in test:
            version_field=test["version"]
        uuid_field = "uuid"
        if "uuid_field" in test:
            uuid_field=test["uuid_field"]

        utils = Utils(uuid_field, version_field)
        datasource = utils.get_datasource(config_map)
        matcher = Matcher(
            index=test["index"],
            level=logger_instance.level,
            es_url=datasource,
            verify_certs=False,
            version_field=version_field,
            uuid_field=uuid_field
        )

        start_timestamp = get_start_timestamp(kwargs)
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
            logger_instance.error("No algorithm configured")
            return None, None
        logger_instance.info("Comparison algorithm: %s", algorithm_name)

        algorithmFactory = AlgorithmFactory()
        
        algorithm = algorithmFactory.instantiate_algorithm(
                algorithm_name,
                matcher,
                fingerprint_matched_df,
                test,
                kwargs,
                metrics_config,
            )
        testname, result_data, test_flag = algorithm.output(kwargs["output_format"])
        result_output[testname] = result_data
        regression_flag = regression_flag or test_flag
    return result_output, regression_flag


def get_start_timestamp(kwargs: Dict[str, Any]) -> str:
    """Get the start timestamp if lookback is provided."""
    return (
        get_subtracted_timestamp(kwargs["lookback"]) if kwargs.get("lookback") else ""
    )
