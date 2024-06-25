"""
run test
"""

import logging
from fmatch.matcher import Matcher
import pandas as pd
from pkg.algorithmFactory import AlgorithmFactory
from pkg.logrus import SingletonLogger
import pkg.constants as cnsts
from pkg.utils import get_es_url, process_test, get_subtracted_timestamp



def run(**kwargs):
    """run method to start the tests

    Args:
        config (_type_): file path to config file
        output_path (_type_): output path to save the data
        hunter_analyze (_type_): changepoint detection through hunter. defaults to True
        output_format (_type_): output to be table or json

    Returns:
        _type_: _description_
    """
    logger_instance = SingletonLogger(debug=logging.INFO).logger
    data = kwargs["configMap"]

    ES_URL = get_es_url(data)
    result_output = {}
    for test in data["tests"]:
        match = Matcher(
            index=test["index"],
            level=logger_instance.level,
            ES_URL=ES_URL,
            verify_certs=False,
        )
        metrics_config={}
        result_dataframe = process_test(
            test,
            match,
            kwargs["save_data_path"],
            kwargs["uuid"],
            kwargs["baseline"],
            metrics_config
        )
        if result_dataframe is None:
            return None
        if kwargs["lookback"]:
            start_timestamp = get_subtracted_timestamp(kwargs["lookback"])
            result_dataframe['timestamp'] = pd.to_datetime(result_dataframe['timestamp'])
            result_dataframe=result_dataframe[result_dataframe["timestamp"] > start_timestamp]
        result_dataframe = result_dataframe.reset_index(drop=True)
        algorithm_name=None
        if kwargs["hunter_analyze"]:
            algorithmFactory = AlgorithmFactory()
            algorithm = algorithmFactory.instantiate_algorithm(
                cnsts.EDIVISIVE, match, result_dataframe, test, kwargs, metrics_config
            )
            testname, result_data = algorithm.output(kwargs["output_format"])
            result_output[testname] = result_data
        elif kwargs["anomaly_detection"]:
            algorithmFactory = AlgorithmFactory()
            algorithm = algorithmFactory.instantiate_algorithm(
                cnsts.ISOLATION_FOREST, match, result_dataframe, test, kwargs, metrics_config
            )
            testname, result_data = algorithm.output(kwargs["output_format"])
            result_output[testname] = result_data
    return result_output
