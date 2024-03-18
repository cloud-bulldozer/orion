"""
run test
"""
from fmatch.matcher import Matcher
from pkg.logrus import SingletonLogger
from pkg.utils import (
    run_hunter_analyze,
    load_config,
    get_es_url,
    process_test
)

logger_instance= SingletonLogger().logger

def run(config, output_path, hunter_analyze,output_format):
    """run method to start the tests

    Args:
        config (_type_): file path to config file
        debug (_type_): debug to be true or false
        output_path (_type_): output path to save the data
        hunter_analyze (_type_): changepoint detection through hunter. defaults to True
        output_format (_type_): output to be table or json

    Returns:
        _type_: _description_
    """
    data = load_config(config, logger_instance)
    ES_URL = get_es_url(data,logger=logger_instance)
    result_output = {}
    for test in data["tests"]:
        match = Matcher(index="perf_scale_ci",level=logger_instance.level, ES_URL=ES_URL)
        result = process_test(test, match, logger_instance, output_path)
        if hunter_analyze:
            testname,result_data=run_hunter_analyze(result, test,output=output_format,matcher=match)
            result_output[testname]=result_data
    return result_output
