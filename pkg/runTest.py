"""
run test
"""

import logging
from fmatch.matcher import Matcher
from pkg.algorithmFactory import AlgorithmFactory
from pkg.logrus import SingletonLogger
from pkg.utils import get_es_url, process_test
from pkg.types import OptionMap
import pkg.constants as cnsts

def run():
    """run method to start the tests

    Args:
        config (_type_): file path to config file
        output_path (_type_): output path to save the data
        hunter_analyze (_type_): changepoint detection through hunter. defaults to True
        output_format (_type_): output to be table or json

    Returns:
        _type_: _description_
    """
    optionMap= OptionMap.get_map()
    logger_instance = SingletonLogger(debug=logging.INFO).logger
    data = optionMap["configMap"]

    ES_URL = get_es_url(data)
    result_output = {}
    for test in data["tests"]:
        match = Matcher(
            index=test["index"],
            level=logger_instance.level,
            ES_URL=ES_URL,
            verify_certs=False,
        )
        result_dataframe = process_test(
            test, match, optionMap["output_path"], optionMap["uuid"], optionMap["baseline"]
        )
        if result_dataframe is None:
            return None
        result_dataframe = result_dataframe.reset_index(drop=True)
        if optionMap["hunter_analyze"]:
            algorithmFactory = AlgorithmFactory()
            algorithm = algorithmFactory.instantiate_algorithm(
                cnsts.EDIVISIVE, match, result_dataframe, test
            )
            testname, result_data = algorithm.output(optionMap["output_format"])
            result_output[testname] = result_data
        elif optionMap["anomaly_detection"]:
            algorithmFactory = AlgorithmFactory()
            algorithm = algorithmFactory.instantiate_algorithm(
                cnsts.ISOLATION_FOREST, match, result_dataframe, test
            )
            testname, result_data = algorithm.output(optionMap["output_format"])
            result_output[testname] = result_data
    return result_output
