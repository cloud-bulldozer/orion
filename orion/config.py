# pylint: disable = line-too-long
"""
Module file for config reading and loading
"""

import sys
import os
from typing import Any, Dict

import jinja2
import yaml
from orion.logger import SingletonLogger


def load_config(config_path: str, input_vars: Dict[str, Any]) -> Dict[str, Any]:
    """Loads config file

    Args:
        config_path (str): file path to config file
        input_vars (Dict[str, Any]): dictionary of input variables

    Returns:
        Dict[str, Any]: dictionary of the config file
    """
    logger = SingletonLogger.get_logger("Orion")
    env_vars = {k.lower(): v for k, v in os.environ.items()}
    env_vars.update(input_vars)
    template_content = load_read_file(config_path, logger)
    rendered_config = render_template(template_content, env_vars, logger)
    
    # Extract parentConfig and metricsFile fields if they exist
    parent_config = None
    metrics_file = None
    
    # Get the directory of the config file for resolving relative paths
    config_dir = os.path.dirname(os.path.abspath(config_path))
    print(config_dir)
    
    if "parentConfig" in rendered_config:
        parent_config = load_parent_config(
            rendered_config["parentConfig"],
            config_dir,
            env_vars,
            logger
        )
        print(parent_config)
    
    if "metricsFile" in rendered_config:
        metrics = load_metrics_file(
            rendered_config["metricsFile"],
            config_dir,
            env_vars,
            logger
        )
        print(metrics)

    print(rendered_config)
    return rendered_config

def load_ack(ack: str) -> Dict[str,Any]:
    """Loads acknowledgment file content.

    Args:
        ack (str): path to the acknowledgment file

    Returns:
        dict: dictionary of the acknowledgment file
    """
    logger = SingletonLogger.get_logger("Orion")
    template_content = load_read_file(ack, logger)
    try:
        rendered_config = yaml.safe_load(template_content)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("An error occurred: %s", e)
        sys.exit(1)
    # Empty rendered config
    if rendered_config is None:
        return rendered_config
    # Ensure the ack file is properly setup.
    if "ack" not in rendered_config:
        logger.error("Ack file not setup properly")
        sys.exit(1)
    return rendered_config


def load_parent_config(parent_config: str, 
                    config_dir: str, 
                    env_vars: Dict[str, Any], 
                    logger: SingletonLogger) -> Dict[str, Any]:
    """Loads parent config file content.

    Args:
        parent_config (str): path to the parent config file
        config_dir (str): directory of the config file
        env_vars (Dict[str, Any]): dictionary of input variables
        logger (SingletonLogger): logger instance
    """
    # Determine if path is absolute or relative
    if os.path.isabs(parent_config):
        parent_config_path = parent_config
    else:
        # Resolve relative path relative to config file directory
        parent_config_path = os.path.join(config_dir, parent_config)
    parent_config_content = load_read_file(parent_config_path, logger)
    # Load YAML content from parentConfig file
    return render_template(parent_config_content, env_vars, logger)

def load_metrics_file(metrics_file: str, 
                    config_dir: str, 
                    env_vars: Dict[str, Any], 
                    logger: SingletonLogger) -> Dict[str, Any]:
    """Loads metrics file content.

    Args:
        metrics_file (str): path to the metrics file
        config_dir (str): directory of the config file
        env_vars (Dict[str, Any]): dictionary of input variables
        logger (SingletonLogger): logger instance
    """
    # Determine if path is absolute or relative
    if os.path.isabs(metrics_file):
        metrics_file_path = metrics_file
    else:
        # Resolve relative path relative to config file directory
        metrics_file_path = os.path.join(config_dir, metrics_file)
    metrics_file_content = load_read_file(metrics_file_path, logger)
    # Load YAML content from metricsFile
    # Render with Jinja2 if it contains templates
    return render_template(metrics_file_content, env_vars, logger)

def load_read_file(file_path: str, logger: SingletonLogger) -> str:
    """Loads file content.

    Args:
        file_path (str): path to the file
        logger (SingletonLogger): logger instance
    """
    try:
        with open(file_path, "r", encoding="utf-8") as template_file:
            template_content = template_file.read()
            logger.debug("The %s file has successfully loaded", file_path)
            return template_content
    except FileNotFoundError as e:
        logger.error("File %s not found: %s", file_path, e)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("An error occurred with file %s: %s", file_path, e)
        sys.exit(1)


def render_template(template: str, env_vars: Dict[str, Any], logger: SingletonLogger) -> Dict[str, Any]:
    """Renders a template with Jinja2.

    Args:
        template (str): template to render
        env_vars (Dict[str, Any]): dictionary of input variables
        logger (SingletonLogger): logger instance
    """
    template = jinja2.Template(template, undefined=jinja2.StrictUndefined)
    try:
        rendered_config_yaml = template.render(env_vars)
    except jinja2.exceptions.UndefinedError as e:
        logger.critical("Jinja rendering error: %s, define it through the input-variables flag", e)
        sys.exit(1)
    return yaml.safe_load(rendered_config_yaml)