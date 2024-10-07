"""
run test
"""

import asyncio
import sys
from typing import Any, Dict
from fmatch.logrus import SingletonLogger
from pkg.algorithms import AlgorithmFactory
import pkg.constants as cnsts
from pkg.utils import get_datasource, get_subtracted_timestamp
from pkg.datasources import DatasourceFactory


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


async def run(**kwargs: dict[str, Any]) -> dict[str, Any]:  # pylint: disable = R0914
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
    fingerprint_matched_df, metrics_config = None, None
    for test in config_map["tests"]:
        # Create fingerprint Matcher
        start_timestamp = get_start_timestamp(kwargs)
        datasourceFactory = DatasourceFactory()
        datasource_object, matcher = datasourceFactory.instantiate_datasource(
            datasource=datasource,
            test=test,
            options=kwargs,
            start_timestamp=start_timestamp,
        )
        if asyncio.iscoroutinefunction(datasource_object.process_test):
            fingerprint_matched_df, metrics_config = (
                await datasource_object.process_test()
            )
        else:
            fingerprint_matched_df, metrics_config = datasource_object.process_test()

        if fingerprint_matched_df is None:
            sys.exit(3)  # No data present
        logger_instance.debug(
            f"Collected dataframe {fingerprint_matched_df},\n metrics {metrics_config}"
        )

        algorithm_name = get_algorithm_type(kwargs)
        if algorithm_name is None:
            return None, None

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
        logger_instance.debug(f"Result data for test {testname}, {result_data}")
        result_output[testname] = result_data
        regression_flag = regression_flag or test_flag
    return result_output, regression_flag


def get_start_timestamp(kwargs: Dict[str, Any]) -> str:
    """Get the start timestamp if lookback is provided."""
    return (
        get_subtracted_timestamp(kwargs["lookback"]) if kwargs.get("lookback") else ""
    )
