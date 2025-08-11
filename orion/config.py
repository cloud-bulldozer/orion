# pylint: disable = line-too-long
"""
Module file for config reading and loading
"""


import os
import sys
from typing import Any, Dict, Set

import jinja2
import yaml
from orion.logger import SingletonLogger


def load_config(config_path: str, input_vars: Dict[str, Any]) -> Dict[str, Any]:
    """Loads config file

    Args:
    **kwargs: keyword arguments
        config (str): file path to config file

    Returns:
        dict: dictionary of the config file
    """
    logger = SingletonLogger.get_logger("Orion")
    try:
        with open(config_path, "r", encoding="utf-8") as template_file:
            template_content = template_file.read()
            logger.debug("File %s loaded successfully", config_path)
    except FileNotFoundError as e:
        logger.error("Config file not found: %s", e)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("An error occurred: %s", e)
        sys.exit(1)
    template = jinja2.Template(template_content, undefined=jinja2.StrictUndefined)
    try:
        rendered_config_yaml = template.render(input_vars)
    except jinja2.exceptions.UndefinedError as e:
        logger.critical("Jinja rendering error: %s, define it through the input-variables flag", e)
        sys.exit(1)
    rendered_config = yaml.safe_load(rendered_config_yaml)
    return rendered_config

def load_ack(ack: str) -> Dict[str,Any]:
    "Loads acknowledgment file content."
    logger = SingletonLogger.get_logger("Orion")
    try:
        with open(ack, "r", encoding="utf-8") as template_file:
            template_content = template_file.read()
            logger.debug("The %s file has successfully loaded", ack)
    except FileNotFoundError as e:
        logger.error("Config file not found: %s", e)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("An error occurred: %s", e)
        sys.exit(1)

    rendered_config = yaml.safe_load(template_content)
    return rendered_config
