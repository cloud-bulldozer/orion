# pylint: disable = line-too-long
"""
Module file for config reading and loading
"""


import os
import sys
from typing import Any, Dict, Set

from jinja2 import Environment, Template, meta
from fmatch.logrus import SingletonLogger
import yaml


def load_config(config: str, parameters: Dict= None) -> Dict[str, Any]:
    """Loads config file

    Args:
        config (str): path to config file
        logger (Logger): logger

    Returns:
        dict: dictionary of the config file
    """
    env_vars = {k.lower(): v for k, v in os.environ.items()}
    merged_parameters = {}
    merged_parameters.update(env_vars)
    if parameters:
        merged_parameters.update(parameters)
    logger_instance = SingletonLogger.getLogger("Orion")
    try:
        with open(config, "r", encoding="utf-8") as template_file:
            template_content = template_file.read()
            logger_instance.debug("The %s file has successfully loaded", config)
    except FileNotFoundError as e:
        logger_instance.error("Config file not found: %s", e)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger_instance.error("An error occurred: %s", e)
        sys.exit(1)

    required_parameters = get_template_variables(template_content)
    logger_instance.debug(f"Variables required by the template: {required_parameters}")

    # Check for missing variables
    missing_vars = required_parameters - merged_parameters.keys()
    if missing_vars:
        logger_instance.error(f"Missing required parameters: {missing_vars}, use environment variables to set")
        sys.exit(1)

    template = Template(template_content)
    rendered_config_yaml = template.render(merged_parameters)
    rendered_config = yaml.safe_load(rendered_config_yaml)
    return rendered_config

def load_ack(ack: str) -> Dict[str,Any]:
    """Loads ack file

    Args:
        config (str): path to config file

    Returns:
        dict: dictionary of the config file
    """

    logger_instance = SingletonLogger.getLogger("Orion")
    try:
        with open(ack, "r", encoding="utf-8") as template_file:
            template_content = template_file.read()
            logger_instance.debug("The %s file has successfully loaded", ack)
    except FileNotFoundError as e:
        logger_instance.error("Config file not found: %s", e)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger_instance.error("An error occurred: %s", e)
        sys.exit(1)

    rendered_config = yaml.safe_load(template_content)
    return rendered_config

def get_template_variables(template_content: str) -> Set[str]:
    """Extracts all variables from the Jinja2 template content."""
    env = Environment()
    parsed_content = env.parse(template_content)
    variables = meta.find_undeclared_variables(parsed_content)
    return variables
