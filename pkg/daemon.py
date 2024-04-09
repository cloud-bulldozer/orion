"""
Module to run orion in daemon mode
"""

import logging

from fastapi import FastAPI
from jinja2 import Template
import yaml
from pkg.logrus import SingletonLogger

from . import runTest

app = FastAPI()
logger_instance = SingletonLogger(debug=logging.INFO).logger


@app.post("/daemon")
async def daemon(
    version: str = "4.15",
    uuid: str = "",
    baseline: str = "",
    filter_changepoints="",
):
    """starts listening on port 8000 on url /daemon

    Args:
        file (UploadFile, optional): config file for the test. Defaults to File(...).

    Returns:
        json: json object of the changepoints and metrics
    """
    config_file_name="configs/small-scale-cluster-density.yml"
    parameters={
        "version": version
    }
    argDict = {
        "config": config_file_name,
        "output_path": "output.csv",
        "hunter_analyze": True,
        "output_format": "json",
        "uuid": uuid,
        "baseline": baseline,
        "configMap": render_template(config_file_name, parameters)
    }
    filter_changepoints = (
        True if filter_changepoints == "true" else False # pylint: disable = R1719
    )
    result = runTest.run(**argDict)
    if filter_changepoints:
        for key, value in result.items():
            result[key] = list(filter(lambda x: x.get("is_changepoint", False), value))
    return result

def render_template(file_name, parameters):
    """replace parameters in the config file

    Args:
        file_name (str): the config file
        parameters (dict): parameters to be replaces

    Returns:
        dict: configMap in dict
    """
    with open(file_name, 'r', encoding="utf-8") as template_file:
        template_content = template_file.read()
    template = Template(template_content)
    rendered_config_yaml = template.render(parameters)
    rendered_config = yaml.safe_load(rendered_config_yaml)
    return rendered_config
