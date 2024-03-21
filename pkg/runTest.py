"""
run test
"""

import logging
from fmatch.matcher import Matcher
from pkg.logrus import SingletonLogger
from pkg.utils import run_hunter_analyze, load_config, get_es_url, process_test


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
    data = load_config(kwargs["config"])
    ES_URL = get_es_url(data)
    result_output = {}
    for test in data["tests"]:
        match = Matcher(
            index="perf_scale_ci", level=logger_instance.level, ES_URL=ES_URL
        )
        result = process_test(
            test, match, kwargs["output_path"], kwargs["uuid"], kwargs["baseline"]
        )
        if kwargs["hunter_analyze"]:
            testname, result_data = run_hunter_analyze(
                result, test, output=kwargs["output_format"], matcher=match
            )
            result_output[testname] = result_data
        del match
    return result_output
