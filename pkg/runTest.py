"""
run test
"""
from typing import Any, Dict
from fmatch.matcher import Matcher
from fmatch.logrus import SingletonLogger
from pkg.algorithms import AlgorithmFactory
import pkg.constants as cnsts
from pkg.utils import get_datasource, process_test, get_subtracted_timestamp



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
    datasource = get_datasource(config_map)
    result_output = {}
    regression_flag = False
    for test in config_map["tests"]:
        # Create fingerprint Matcher
        matcher = Matcher(
            index=test["index"],
            level=logger_instance.level,
            ES_URL=datasource,
            verify_certs=False,
        )
        start_timestamp = get_start_timestamp(kwargs)

        fingerprint_matched_df, metrics_config = process_test(
            test,
            matcher,
            kwargs,
            start_timestamp,
        )
        if fingerprint_matched_df is None:
            return None

        if kwargs["hunter_analyze"]:
            algorithm_name = cnsts.EDIVISIVE
        elif kwargs["anomaly_detection"]:
            algorithm_name = cnsts.ISOLATION_FOREST
        else:
            return None

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
